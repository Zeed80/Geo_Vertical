<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" >

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="html" omit-xml-declaration="no"  encoding="utf-8"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="DegreesSymbol" select="'&#0176;'"/>
<xsl:variable name="MinutesSymbol"><xsl:text>'</xsl:text></xsl:variable>
<xsl:variable name="SecondsSymbol" select="'&quot;'"/>

<xsl:variable name="fileExt" select="'htm'"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->

<xsl:variable name="userField1" select="'HzSOTol|Stakeout horizontal tolerance|double|0.0|1.0'"/>
<xsl:variable name="HzSOTol" select="0.02"/>
<xsl:variable name="userField2" select="'VtSOTol|Stakeout vertical tolerance|double|0.0|1.0'"/>
<xsl:variable name="VtSOTol" select="0.05"/>
<xsl:variable name="userField3" select="'TolCheckType|Tolerance check|stringMenu|3|Hz tolerance check|Vt tolerance check|Both'"/>
<xsl:variable name="TolCheckType" select="'Both'"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <HTML>

  <Title>Stakeout Tolerance Report</Title>
  <h2>Stakeout Tolerance Report</h2>

  <HEAD>
  </HEAD>

  <BODY>
  <TABLE BORDER="0" width="100%" cellpadding="5">
    <TR>
      <TD>Job name:</TD>
      <TD><xsl:value-of select="JOBFile/@jobName"/></TD>
    </TR>
    <TR>
      <TD><xsl:value-of select="JOBFile/@product"/> version:</TD>
      <TD><xsl:value-of select="JOBFile/@productVersion"/></TD>
    </TR>
    <xsl:if test="JOBFile/@TimeStamp != ''"> <!-- Date could be null in an updated job -->
      <TR>
        <TD>Creation date:</TD>
        <TD><xsl:value-of select="substring-before(JOBFile/@TimeStamp, 'T')"/></TD>
      </TR>
    </xsl:if>
    <TR>
      <TD>Distance/Coord units:</TD>
      <TD><xsl:value-of select="$DistUnit"/></TD>
    </TR>
    <TR>
      <TD>Angle units:</TD>
      <TD><xsl:value-of select="$AngleUnit"/></TD>
    </TR>
    <TR>
      <TD>Stakeout horizontal tolerance:</TD>
      <TD><xsl:value-of select="format-number(number($HzSOTol), $DecPl3, 'Standard')"/></TD>
    </TR>
    <TR>
      <TD>Stakeout vertical tolerance:</TD>
      <TD><xsl:value-of select="format-number(number($VtSOTol), $DecPl3, 'Standard')"/></TD>
    </TR>
    <TR>
      <TD>Tolerance checking/highlighting:</TD>
      <TD><xsl:value-of select="$TolCheckType"/></TD>
    </TR>
  </TABLE>  
  
  <xsl:call-template name="SeparatingLine"/>
  <BR/>
  <TABLE border="1" width="100%" cellpadding="2">
    <CAPTION><xsl:value-of select="'Highlighted values exceed stakeout tolerances.'"/></CAPTION>
    <THEAD>
      <TR>
        <TD width="37%" align="center"><SMALL><B>Name</B></SMALL></TD>
        <xsl:if test="$NECoords = 'true'">
          <TD width="15%" align="center"><SMALL><B>dNorth</B></SMALL></TD>
          <TD width="15%" align="center"><SMALL><B>dEast</B></SMALL></TD>
        </xsl:if>
        <xsl:if test="$NECoords = 'false'">
          <TD width="15%" align="center"><SMALL><B>dEast</B></SMALL></TD>
          <TD width="15%" align="center"><SMALL><B>dNorth</B></SMALL></TD>
        </xsl:if>
        <TD width="15%" align="center"><SMALL><B>dElev</B></SMALL></TD>
        <TD width="18%" align="center"><SMALL><B>Code</B></SMALL></TD>
      </TR>
    </THEAD>
    <TBODY>
    <!-- Select the FieldBook node to process -->
    <xsl:apply-templates select="JOBFile/FieldBook" />

    </TBODY>
  </TABLE>
  </BODY>
  </HTML>
</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">
<!-- Process the records under the FieldBook node in the order encountered -->
  <xsl:for-each select="*">
    <xsl:choose>
      <!-- Handle Point record -->
      <xsl:when test="name(current()) = 'PointRecord'">
        <xsl:apply-templates select="current()"/> 
      </xsl:when>
    </xsl:choose>
  </xsl:for-each>
</xsl:template>


<!-- **************************************************************** -->
<!-- ******************** PointRecord Output ************************ -->
<!-- **************************************************************** -->
<xsl:template match="PointRecord">
  <xsl:if test="Deleted = 'false'">  <!-- only output if not deleted -->

    <xsl:if test="Stakeout">
      <xsl:call-template name="StakeoutDeltas"/> 
    </xsl:if>

  </xsl:if>
</xsl:template>


<!-- **************************************************************** -->
<!-- ************** Stakeout Deltas Details Output ****************** -->
<!-- **************************************************************** -->
<xsl:template name="StakeoutDeltas">
  <xsl:variable name="dNthStr" select="format-number(Stakeout/GridDeltas/DeltaNorth * $DistConvFactor, $DecPl3, 'Standard')"/>

  <xsl:variable name="dEastStr" select="format-number(Stakeout/GridDeltas/DeltaEast * $DistConvFactor, $DecPl3, 'Standard')" />

  <xsl:variable name="dElevStr" select="format-number(Stakeout/GridDeltas/DeltaElevation * $DistConvFactor, $DecPl3, 'Standard')"/>

  <!-- Create absolute value delta elevation equivalent for tolerance
       testing purposes -->
  <xsl:variable name="dAbsElev" select="concat(substring('-',2 - ((Stakeout/GridDeltas/DeltaElevation * $DistConvFactor) &lt; 0)), '1') * (Stakeout/GridDeltas/DeltaElevation * $DistConvFactor)"/>

  <xsl:variable name="PolarDeltaSq" select="(Stakeout/GridDeltas/DeltaNorth * Stakeout/GridDeltas/DeltaNorth + 
                                             Stakeout/GridDeltas/DeltaEast * Stakeout/GridDeltas/DeltaEast) *
                                             $DistConvFactor * $DistConvFactor"/>

  <TR>
    <TD width="37%" align="left"><SMALL><xsl:value-of select="Name"/></SMALL></TD>

    <xsl:choose>
      <xsl:when test="(($TolCheckType = 'Hz tolerance check') or ($TolCheckType = 'Both')) and
                      ($PolarDeltaSq > $HzSOTol * $HzSOTol)">
        <xsl:if test="$NECoords = 'true'">
          <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dNthStr"/></SMALL></B></FONT></TD>
          <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dEastStr"/></SMALL></B></FONT></TD>
        </xsl:if>
        <xsl:if test="$NECoords = 'false'">
          <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dEastStr"/></SMALL></B></FONT></TD>
          <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dNthStr"/></SMALL></B></FONT></TD>
        </xsl:if>
      </xsl:when>
      <xsl:otherwise>
        <xsl:if test="$NECoords = 'true'">
          <TD width="15%" align="right"><SMALL><xsl:value-of select="$dNthStr"/></SMALL></TD>
          <TD width="15%" align="right"><SMALL><xsl:value-of select="$dEastStr"/></SMALL></TD>
        </xsl:if>
        <xsl:if test="$NECoords = 'false'">
          <TD width="15%" align="right"><SMALL><xsl:value-of select="$dEastStr"/></SMALL></TD>
          <TD width="15%" align="right"><SMALL><xsl:value-of select="$dNthStr"/></SMALL></TD>
        </xsl:if>
      </xsl:otherwise>
    </xsl:choose>

    <xsl:choose>
      <xsl:when test="(($TolCheckType = 'Vt tolerance check') or ($TolCheckType = 'Both')) and
                      ($dAbsElev > $VtSOTol)">
        <TD width="15%" align="right"><FONT color="red"><B><SMALL><xsl:value-of select="$dElevStr"/></SMALL></B></FONT></TD>
      </xsl:when>
      <xsl:otherwise>
        <TD width="15%" align="right"><SMALL><xsl:value-of select="$dElevStr"/></SMALL></TD>
      </xsl:otherwise>
    </xsl:choose>
    <TD width="18%" align="left"><SMALL><xsl:value-of select="Code"/></SMALL></TD>
  </TR>

</xsl:template>


<!-- **************************************************************** -->
<!-- ****************** Separating Line Output ********************** -->
<!-- **************************************************************** -->
<xsl:template name="SeparatingLine">
  <hr/>
</xsl:template>


</xsl:stylesheet>